import { app, BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { assertUserDataDir, userDataDir } from "./compat-paths";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── DATA-01: lock del data dir ANTES de cualquier acceso a paths ──
// Orden crítico: sin esto Electron usaría %APPDATA%\Nyanko (productName) y la
// biblioteca de prod existente quedaría huérfana.
app.setPath("userData", userDataDir(app.getPath("appData")));
assertUserDataDir(app.getPath("userData"));

function createWindow(): void {
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

  win.on("ready-to-show", () => win.show());

  // Dual-path estándar de electron-vite: dev sirve desde el vite server, prod
  // carga el index.html construido.
  const devUrl = process.env["ELECTRON_RENDERER_URL"];
  if (devUrl) {
    win.loadURL(devUrl);
  } else {
    win.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  // Windows es el target primario: salir al cerrar todas las ventanas.
  app.quit();
});
