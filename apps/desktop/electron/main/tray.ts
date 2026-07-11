import { app, Tray, Menu, nativeImage, BrowserWindow } from "electron";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

// Paridad D-06/D-07 con el viejo tray.rs: bandeja con el ícono de marca (D-07,
// build/icon.png — sin ícono monocromo dedicado) y menú en español. Convención de
// Windows: menú con click derecho; el doble click (izq) muestra la app.

const __dirname = dirname(fileURLToPath(import.meta.url));

let tray: Tray | null = null;
// Estado de detección en memoria (equivale a DetectionPaused del Rust). La etiqueta
// del ítem refleja este booleano.
let detectionPaused = false;

// Resuelve la URL del sidecar local: puerto dinámico en userData/port, fallback
// 8765. NUNCA acepta host/puerto del renderer (T-04-06: solo 127.0.0.1 local).
// ponytail: read-file/parseInt/fallback trivial — sin test dedicado (YAGNI), lo
// ejercita el verify de fase.
function resolveApiUrl(): string {
  try {
    const port = parseInt(
      readFileSync(join(app.getPath("userData"), "port"), "utf-8").trim(),
      10,
    );
    if (Number.isInteger(port) && port > 0) return `http://127.0.0.1:${port}`;
  } catch {
    // sin fichero port → fallback
  }
  return "http://127.0.0.1:8765";
}

function showWindow(win: BrowserWindow | null): void {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

// POST al sidecar local /api/detection/{pause|resume} con timeout de 5s. En error
// HTTP: log y NO cambia de estado (mirror tray.rs). En éxito: cambia el booleano,
// reconstruye la etiqueta del menú y avisa al renderer (detection-paused).
async function toggleDetection(
  paused: boolean,
  getMainWindow: () => BrowserWindow | null,
  rebuildMenu: () => void,
): Promise<void> {
  const url = `${resolveApiUrl()}/api/detection/${paused ? "pause" : "resume"}`;
  try {
    const res = await fetch(url, { method: "POST", signal: AbortSignal.timeout(5000) });
    if (!res.ok) {
      console.error(`Fallo al alternar detección: HTTP ${res.status}`);
      return;
    }
  } catch (err) {
    console.error(`Fallo al alternar detección: ${String(err)}`);
    return;
  }
  detectionPaused = paused;
  rebuildMenu();
  getMainWindow()?.webContents.send("detection-paused", paused);
}

// setupTray monta la bandeja una sola vez. El getter de la ventana lo aporta
// index.ts (guarda mainWindow tras createWindow).
export function setupTray(getMainWindow: () => BrowserWindow | null): Tray | null {
  if (tray) return tray; // idempotente: Retry del splash no duplica la bandeja
  const icon = nativeImage.createFromPath(join(__dirname, "../../build/icon.png"));
  tray = new Tray(icon);
  tray.setToolTip("Nyanko");

  const rebuildMenu = () => {
    tray?.setContextMenu(
      Menu.buildFromTemplate([
        { label: "Mostrar", click: () => showWindow(getMainWindow()) },
        { label: "Ocultar", click: () => getMainWindow()?.hide() },
        {
          label: detectionPaused ? "Reanudar detección" : "Pausar detección",
          click: () => void toggleDetection(!detectionPaused, getMainWindow, rebuildMenu),
        },
        { type: "separator" },
        // Salir hace app.quit(): before-quit (index.ts) marca isQuitting y mata el
        // sidecar por el MISMO camino existente — no se duplica killSidecar.
        { label: "Salir", click: () => app.quit() },
      ]),
    );
  };

  rebuildMenu();
  // Doble click (izq) muestra+enfoca la ventana (menú queda en click derecho).
  tray.on("double-click", () => showWindow(getMainWindow()));
  return tray;
}
