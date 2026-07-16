import { BrowserWindow } from "electron";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// D-01/D-06: splash inmediato (nunca app congelada) mientras el main spawnea el
// sidecar y espera readiness. En fallo pasa a estado de error con Reintentar /
// Abrir logs / Salir. Es una ventana PRE-renderer sin i18n runtime: HTML/CSS/JS
// plano, dependency-free, sin entry de bundler.

// T-02-SPLASH: MISMAS webPreferences seguras que la ventana principal + el mismo
// preload endurecido (nyanko bridge). No se introduce ninguna ventana privilegiada.
// El splash no carga nada externo: default-src 'none' cierra toda salida. El script
// inline se limita a los tres onclick de Reintentar/Abrir logs/Salir; bloquearlos
// dejaria sin respuesta precisamente la pantalla que aparece cuando algo ya fallo.
const SPLASH_HTML = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'" />
<style>
  html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif;
    background: #14131a; color: #ece9f1; -webkit-user-select: none; user-select: none; }
  body { display: flex; align-items: center; justify-content: center; }
  .panel { text-align: center; padding: 24px; max-width: 340px; }
  .loading .spinner { width: 28px; height: 28px; margin: 0 auto 14px;
    border: 3px solid #3a3550; border-top-color: #a88bff; border-radius: 50%;
    animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error { display: none; }
  body[data-state="error"] .loading { display: none; }
  body[data-state="error"] .error { display: block; }
  .error h1 { font-size: 15px; margin: 0 0 6px; }
  .error p { font-size: 12px; color: #b7b1c6; margin: 0 0 16px; }
  .row { display: flex; gap: 8px; justify-content: center; }
  button { font: inherit; font-size: 12px; padding: 6px 12px; border-radius: 6px;
    border: 1px solid #3a3550; background: #211d2e; color: #ece9f1; cursor: pointer; }
  button.primary { background: #6f4ee0; border-color: #6f4ee0; }
</style>
</head>
<body>
  <div class="panel loading">
    <div class="spinner"></div>
    <div>Iniciando Nyanko…</div>
  </div>
  <div class="panel error">
    <h1>No se pudo iniciar Nyanko</h1>
    <p>El servicio local no respondió. Revisa los registros para ver el detalle.</p>
    <div class="row">
      <button class="primary" onclick="window.nyanko&&window.nyanko.retryStartup()">Reintentar</button>
      <button onclick="window.nyanko&&window.nyanko.openLogsFolder()">Abrir logs</button>
      <button onclick="window.nyanko&&window.nyanko.quit()">Salir</button>
    </div>
  </div>
</body>
</html>`;

export function createSplash(): BrowserWindow {
  const win = new BrowserWindow({
    width: 420,
    height: 300,
    frame: false,
    resizable: false,
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
  void win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(SPLASH_HTML));
  return win;
}

// D-06: revela el panel de error. executeJavaScript evita añadir un canal IPC
// solo para esto (el preload endurecido no expone un ipcRenderer.on genérico).
export function showSplashError(win: BrowserWindow): void {
  if (win.isDestroyed()) return;
  win.webContents.executeJavaScript('document.body.setAttribute("data-state","error")').catch(() => {});
}
