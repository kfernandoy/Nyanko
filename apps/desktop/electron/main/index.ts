import { app, BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { assertUserDataDir, userDataDir } from "./compat-paths";
import { setupLogging } from "./logging";
import { isDevMode, startSidecar, killSidecar } from "./sidecar";
import { createSplash, showSplashError } from "./splash";
import { registerIpc } from "./ipc";
import { seedWindowPrefs, currentWindowPrefs } from "./window-prefs";
import { setupTray } from "./tray";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Ventana principal (la usa la bandeja para mostrar/ocultar) y bandera de salida
// real vs ocultar-a-bandeja: el listener 'close' solo oculta cuando NO salimos.
let mainWindow: BrowserWindow | null = null;
let isQuitting = false;

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
    // D-07: icono de marca ÚNICO (build/icon.png 256x256) reutilizado por la bandeja
    // (Plan 02) y el empaquetado de Fase 5. build/ vive fuera de out/main, de ahí ../../.
    icon: join(__dirname, "../../build/icon.png"),
    show: false,
    webPreferences: {
      preload: join(__dirname, "../preload/index.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  mainWindow = win;

  // NATIVE-04 (paridad lib.rs): cerrar → ocultar a bandeja si close_to_tray y no
  // estamos saliendo de verdad; si no, cierre normal (dispara window-all-closed).
  win.on("close", (e) => {
    if (currentWindowPrefs().close_to_tray && !isQuitting) {
      e.preventDefault();
      win.hide();
    }
  });
  // NATIVE-04 (paridad Resized+is_minimized): minimizar → ocultar a bandeja.
  win.on("minimize", () => {
    if (currentWindowPrefs().minimize_to_tray) win.hide();
  });

  const shown = new Promise<BrowserWindow>((resolve) => {
    win.once("ready-to-show", () => {
      // start_minimized (ajuste o flag --minimized de autostart): paridad lib.rs —
      // la ventana queda oculta (arranca en bandeja) en vez de mostrarse.
      const startMinimized =
        currentWindowPrefs().start_minimized || process.argv.includes("--minimized");
      if (!startMinimized) win.show();
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
    // NATIVE-04: sembrar prefs ANTES de crear la ventana (ready-to-show las lee
    // para decidir start_minimized). Bandeja tras la ventana (mainWindow ya existe).
    seedWindowPrefs(app.getPath("userData"));
    await createWindow();
    setupTray(() => mainWindow);
    if (splashWin && !splashWin.isDestroyed()) splashWin.close();
    splashWin = null;
  } catch {
    // D-06: fallo del sidecar → panel de error del splash (Reintentar/Abrir logs/Salir).
    if (splashWin && !splashWin.isDestroyed()) showSplashError(splashWin);
  }
}

// ── Instancia única (NATIVE-06, paridad plugin single_instance de lib.rs) ──
// Sin esto el segundo proceso salía sin mostrar nada y la app "parecía colgada"
// (además de pelearse por el puerto del sidecar). El perdedor del lock sale; el
// vivo recibe 'second-instance' y trae la ventana al frente (show+unminimize+focus,
// que además la rescata de la bandeja).
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    mainWindow.show();
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    // registerIpc UNA sola vez: ipcMain.handle rechaza handlers duplicados, y el
    // Retry re-corre el gate sin re-registrar.
    registerIpc({ onRetry: () => void runStartup() });
    void runStartup();
  });
}

// D-08: matar el sidecar en cada salida antes de cerrar. Se difiere el quit hasta
// que killSidecar (graceful → taskkill /T /F del árbol) termine — si no, el loop
// muere antes del taskkill y queda un nyanko-api.exe huérfano. El updater de
// Phase 5 llama esta MISMA killSidecar antes de quitAndInstall.
let sidecarKilled = false;
app.on("before-quit", (e) => {
  // before-quit se emite ANTES de cerrar las ventanas: marcar isQuitting aquí basta
  // para que el listener 'close' permita el cierre (Salir de la bandeja, cierre de
  // SO). Reutiliza el MISMO killSidecar — no se duplica.
  isQuitting = true;
  if (sidecarKilled) return;
  e.preventDefault();
  sidecarKilled = true;
  void killSidecar().finally(() => app.quit());
});

app.on("window-all-closed", () => {
  // Windows es el target primario: salir al cerrar todas las ventanas.
  app.quit();
});
