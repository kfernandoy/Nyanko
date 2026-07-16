#!/usr/bin/env node

import { execFile, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { copyFile, mkdir, mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { app, BrowserWindow, ipcMain } from "electron";
import sharp from "sharp";

const __dirname = dirname(fileURLToPath(import.meta.url));
const escritorioDir = resolve(__dirname, "..");
const raizRepo = resolve(escritorioDir, "../..");
const backendDir = join(raizRepo, "apps", "backend");
const rendererHtml = join(escritorioDir, "out", "renderer", "index.html");
const preload = join(escritorioDir, "out", "preload", "index.cjs");
const python = process.platform === "win32"
  ? join(backendDir, ".venv", "Scripts", "python.exe")
  : join(backendDir, ".venv", "bin", "python");

const TOTAL_PAGINAS = 200;
const ANCHO_PAGINA = 2000;
const ALTO_PAGINA = 3000;
const TECHO_RSS_MB = 500;
const CADA_CUANTAS_PAGINAS_MUESTREAR = 10;
const TIMEOUT_SIDECAR_MS = 30_000;
const TIMEOUT_RENDERER_MS = 60_000;

app.commandLine.appendSwitch("js-flags", "--expose-gc");

// Sin este listener vacio, Electron aplica su comportamiento por defecto —cerrar la
// ultima ventana termina la app CON CODIGO 0— y limpiar() destruye la ventana antes
// de app.exit(codigoSalida). Los await de limpiar() ceden el control y ese quit(0)
// gana la carrera: el harness imprimia "-> FALLO" y devolvia 0. Un gate que informa
// del fallo y sale en verde es el falso verde que este plan existe para impedir, asi
// que el codigo de salida tiene que ser SIEMPRE el que decide la medicion.
app.on("window-all-closed", () => {});

let dataDir = null;
let sidecar = null;
let ventana = null;
let salidaSidecar = "";
let errorSidecar = null;

const esperar = (milisegundos) => new Promise((resolvePromise) => {
  setTimeout(resolvePromise, milisegundos);
});

function nombrePagina(indice) {
  return `${String(indice).padStart(3, "0")}.jpg`;
}

async function existeConContenido(ruta) {
  try {
    return (await stat(ruta)).size > 0;
  } catch {
    return false;
  }
}

async function prepararBibliotecaTemporal(directorio) {
  const cache = join(tmpdir(), "nyanko-reader-rss-2000x3000-v1");
  const capitulo = join(directorio, "biblioteca", "Serie", "Cap 1");
  await mkdir(cache, { recursive: true });
  await mkdir(capitulo, { recursive: true });

  for (let indice = 1; indice <= TOTAL_PAGINAS; indice += 1) {
    const nombre = nombrePagina(indice);
    const cacheada = join(cache, nombre);
    if (!(await existeConContenido(cacheada))) {
      // Cada fichero cambia de color para impedir que una optimizacion por contenido
      // identico esconda bitmaps. En RAM cada pagina sigue costando 2000x3000x4 bytes.
      await sharp({
        create: {
          width: ANCHO_PAGINA,
          height: ALTO_PAGINA,
          channels: 3,
          background: {
            r: (indice * 47) % 256,
            g: (indice * 83) % 256,
            b: (indice * 131) % 256,
          },
        },
      }).jpeg({ quality: 82 }).toFile(cacheada);
    }
    await copyFile(cacheada, join(capitulo, nombre));
  }
  return join(directorio, "biblioteca");
}

function comprobarPrecondiciones() {
  if (!existsSync(rendererHtml)) {
    throw new Error("falta out/renderer/index.html; ejecuta npm run build antes del harness");
  }
  if (!existsSync(preload)) {
    throw new Error("falta out/preload/index.cjs; ejecuta npm run build antes del harness");
  }
  if (!existsSync(python)) {
    throw new Error(`no existe el Python del venv del backend: ${python}`);
  }
}

function arrancarSidecar(directorio) {
  sidecar = spawn(python, ["sidecar.py"], {
    cwd: backendDir,
    env: {
      ...process.env,
      NYANKO_DATA_DIR: directorio,
      NYANKO_API_HOST: "127.0.0.1",
      NYANKO_API_PORT: "0",
      // El harness nunca debe leer ni usar credenciales reales del usuario.
      PYTHON_KEYRING_BACKEND: "keyring.backends.null.Keyring",
    },
    shell: false,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  sidecar.stdout?.on("data", guardarSalidaSidecar);
  sidecar.stderr?.on("data", guardarSalidaSidecar);
  sidecar.once("error", (error) => { errorSidecar = error; });
}

function guardarSalidaSidecar(fragmento) {
  salidaSidecar = (salidaSidecar + fragmento.toString()).slice(-8_000);
}

function afirmarSidecarVivo() {
  if (errorSidecar) throw new Error(`el sidecar no pudo arrancar: ${errorSidecar.message}`);
  if (!sidecar || sidecar.exitCode !== null) {
    throw new Error(`el sidecar termino antes de tiempo${sidecar ? ` (codigo ${sidecar.exitCode})` : ""}`);
  }
}

async function esperarSidecar(directorio) {
  const archivoPuerto = join(directorio, "port");
  const limite = Date.now() + TIMEOUT_SIDECAR_MS;
  let puerto = null;

  while (Date.now() < limite) {
    afirmarSidecarVivo();
    try {
      const valor = Number((await readFile(archivoPuerto, "utf8")).trim());
      if (Number.isInteger(valor) && valor > 0) {
        puerto = valor;
        break;
      }
    } catch {
      // El lifespan aun no escribio el archivo; seguir esperando.
    }
    await esperar(100);
  }
  if (puerto === null) throw new Error("el sidecar no escribio el archivo de puerto a tiempo");

  while (Date.now() < limite) {
    afirmarSidecarVivo();
    try {
      const respuesta = await fetch(`http://127.0.0.1:${puerto}/api/health`);
      if (respuesta.ok) return puerto;
    } catch {
      // El puerto ya existe, pero uvicorn aun puede estar entrando en readiness.
    }
    await esperar(100);
  }
  throw new Error("el sidecar escribio el puerto pero no respondio /api/health a tiempo");
}

function sembrarEntradaLocalParaElShell(directorio) {
  // App oculta todas las vistas si no hay cuenta ni biblioteca. Esta fila vive solo
  // en la SQLite temporal y evita tocar el llavero o contactar un proveedor real.
  const base = new DatabaseSync(join(directorio, "nyanko.sqlite3"));
  try {
    // El sidecar ya tiene abierta esta MISMA SQLite. Sin busy_timeout la primera
    // escritura choca con su lock y el harness muere con "database is locked" de
    // forma intermitente: un gate que falla al azar acaba reintentandose hasta que
    // sale verde, que es justo como un techo de memoria deja de vigilarse.
    // BEGIN IMMEDIATE coge el lock de escritura al entrar (reintentando durante el
    // busy_timeout) en vez de descubrir el conflicto a mitad de la transaccion.
    base.exec("PRAGMA busy_timeout = 10000");
    base.exec("PRAGMA foreign_keys = ON");
    base.exec("BEGIN IMMEDIATE");
    base.prepare("INSERT OR IGNORE INTO providers(id, display_name) VALUES (?, ?)")
      .run("harness", "Harness local");
    const cuenta = base.prepare(
      "INSERT INTO accounts(provider_id, alias, is_primary) VALUES (?, ?, 1) RETURNING id",
    ).get("harness", "default");
    const medio = base.prepare(
      "INSERT INTO media(media_type, format, episode_count) VALUES ('ANIME', 'TV', 1) RETURNING id",
    ).get();
    base.prepare(
      "INSERT INTO remote_library_entries(account_id, media_id, status, progress, original_payload) "
      + "VALUES (?, ?, 'CURRENT', 0, ?)",
    ).run(cuenta.id, medio.id, JSON.stringify({
      id: 1,
      title: "Entrada local del harness",
      status: "CURRENT",
      progress: 0,
      episodes: 1,
      media_type: "ANIME",
    }));
    base.exec("COMMIT");
  } catch (error) {
    try { base.exec("ROLLBACK"); } catch { /* La transaccion pudo no llegar a abrirse. */ }
    throw error;
  } finally {
    base.close();
  }
}

async function registrarBiblioteca(puerto, directorioBiblioteca, directorio) {
  const token = (await readFile(join(directorio, "instance_token"), "utf8")).trim();
  if (!token) throw new Error("el sidecar no escribio instance_token");
  const respuesta = await fetch(`http://127.0.0.1:${puerto}/api/library/folders`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Nyanko-Instance": token,
    },
    body: JSON.stringify({ path: directorioBiblioteca, recursive: true }),
  });
  if (!respuesta.ok) {
    throw new Error(`POST /api/library/folders fallo: ${respuesta.status} ${await respuesta.text()}`);
  }
}

function registrarIpc(directorio) {
  const archivosLegibles = new Set(["port", "instance_token"]);
  const preferenciasVentana = {
    close_to_tray: false,
    minimize_to_tray: false,
    start_minimized: false,
  };

  ipcMain.handle("readAppDataFile", async (_evento, nombre) => {
    if (typeof nombre !== "string" || !archivosLegibles.has(nombre)) return null;
    try {
      return (await readFile(join(directorio, nombre), "utf8")).trim();
    } catch {
      return null;
    }
  });
  ipcMain.handle("appVersion", () => app.getVersion());
  ipcMain.handle("window-prefs:get", () => preferenciasVentana);
  ipcMain.handle("window-prefs:set", () => preferenciasVentana);
  ipcMain.handle("autostart:get", () => false);
  ipcMain.handle("autostart:set", () => false);

  for (const canal of [
    "openLogsFolder",
    "startup:retry",
    "openExternal",
    "openPath",
    "revealItemInDir",
    "openFolderDialog",
    "notify",
    "window:minimize",
    "window:toggle-maximize",
    "window:close",
    "discord:set-activity",
    "discord:clear-activity",
    "updates:check",
    "updates:install",
  ]) {
    ipcMain.handle(canal, () => null);
  }
  ipcMain.on("startup:quit", () => {});
}

async function abrirAplicacion() {
  const win = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 760,
    minHeight: 560,
    frame: false,
    show: false,
    webPreferences: {
      preload,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  await win.loadFile(rendererHtml, { hash: "local-manga" });
  win.show();
  return win;
}

async function ejecutarEnRenderer(codigo) {
  if (!ventana || ventana.isDestroyed()) throw new Error("la ventana del renderer se cerro");
  return ventana.webContents.executeJavaScript(codigo, true);
}

async function esperarCondicion(codigo, descripcion, timeout = TIMEOUT_RENDERER_MS) {
  const limite = Date.now() + timeout;
  let ultimoError = null;
  while (Date.now() < limite) {
    try {
      if (await ejecutarEnRenderer(codigo)) return;
    } catch (error) {
      ultimoError = error;
    }
    await esperar(100);
  }
  throw new Error(`${descripcion} no ocurrio a tiempo${ultimoError ? `: ${ultimoError.message}` : ""}`);
}

async function abrirPrimerCapitulo() {
  for (let profundidad = 0; profundidad < 4; profundidad += 1) {
    await esperarCondicion(
      "Boolean(document.querySelector('.reader-counter') || document.querySelector('.manga-library-item'))",
      "la biblioteca local no mostro ningun elemento",
    );
    if (await ejecutarEnRenderer("Boolean(document.querySelector('.reader-counter'))")) return;

    const firma = await ejecutarEnRenderer(
      "document.querySelector('.manga-library-item')?.textContent?.trim() ?? ''",
    );
    await ejecutarEnRenderer("document.querySelector('.manga-library-item')?.click(); true");
    await esperarCondicion(
      `Boolean(document.querySelector('.reader-counter')) || `
      + `(document.querySelector('.manga-library-item')?.textContent?.trim() ?? '') !== ${JSON.stringify(firma)}`,
      "la navegacion de la biblioteca no avanzo",
    );
  }
  throw new Error("no se pudo abrir un capitulo desde la biblioteca local");
}

async function esperarPagina(numero) {
  await esperarCondicion(
    `(() => {
      const contador = document.querySelector('.reader-counter')?.textContent?.trim();
      const imagenes = [...document.querySelectorAll('.reader-page--visible img')];
      return contador === '${numero} / ${TOTAL_PAGINAS}'
        && imagenes.length > 0
        && imagenes.every((imagen) => imagen.complete
          && imagen.naturalWidth === ${ANCHO_PAGINA}
          && imagen.naturalHeight === ${ALTO_PAGINA});
    })()`,
    `la pagina ${numero} no termino de cargar`,
  );
}

function enviarTecla(tecla) {
  if (!ventana || ventana.isDestroyed()) throw new Error("la ventana del renderer se cerro");
  ventana.webContents.sendInputEvent({ type: "keyDown", keyCode: tecla });
  ventana.webContents.sendInputEvent({ type: "keyUp", keyCode: tecla });
}

function medirRssRenderer() {
  if (!ventana || ventana.isDestroyed()) throw new Error("la ventana del renderer se cerro");
  const pid = ventana.webContents.getOSProcessId();
  if (!Number.isInteger(pid) || pid <= 0) throw new Error("Electron no devolvio el PID del renderer");
  const metrica = app.getAppMetrics().find((proceso) => proceso.pid === pid);
  if (!metrica || !Number.isFinite(metrica.memory?.workingSetSize)) {
    throw new Error(`getAppMetrics no devolvio el RSS del renderer con PID ${pid}`);
  }
  return metrica.memory.workingSetSize / 1024;
}

async function recorrerCapitulo() {
  await esperarPagina(1);
  let picoRssMB = medirRssRenderer();

  for (let pagina = 2; pagina <= TOTAL_PAGINAS; pagina += 1) {
    enviarTecla("PageDown");
    await esperarPagina(pagina);
    if (pagina % CADA_CUANTAS_PAGINAS_MUESTREAR === 0) {
      picoRssMB = Math.max(picoRssMB, medirRssRenderer());
    }
  }
  for (let pagina = TOTAL_PAGINAS - 1; pagina >= 1; pagina -= 1) {
    enviarTecla("PageUp");
    await esperarPagina(pagina);
    if (pagina % CADA_CUANTAS_PAGINAS_MUESTREAR === 0) {
      picoRssMB = Math.max(picoRssMB, medirRssRenderer());
    }
  }

  const gcDisponible = await ejecutarEnRenderer("typeof globalThis.gc === 'function'");
  if (!gcDisponible) throw new Error("el renderer no expuso gc pese al switch --expose-gc");
  await ejecutarEnRenderer("globalThis.gc(); true");
  await esperar(2_000);
  const rssFinalMB = medirRssRenderer();
  return { rssFinalMB, picoRssMB: Math.max(picoRssMB, rssFinalMB) };
}

async function esperarSalida(proceso, timeout) {
  if (proceso.exitCode !== null) return true;
  return new Promise((resolvePromise) => {
    const temporizador = setTimeout(() => resolvePromise(false), timeout);
    proceso.once("exit", () => {
      clearTimeout(temporizador);
      resolvePromise(true);
    });
  });
}

async function detenerSidecar() {
  const proceso = sidecar;
  sidecar = null;
  if (!proceso || proceso.exitCode !== null || proceso.pid === undefined) return;
  proceso.kill();
  if (await esperarSalida(proceso, 5_000)) return;

  if (process.platform === "win32") {
    await new Promise((resolvePromise) => {
      execFile("taskkill", ["/PID", String(proceso.pid), "/T", "/F"], { windowsHide: true }, () => {
        resolvePromise();
      });
    });
  } else {
    proceso.kill("SIGKILL");
  }
  await esperarSalida(proceso, 5_000);
}

async function limpiar() {
  if (ventana && !ventana.isDestroyed()) ventana.destroy();
  ventana = null;
  await detenerSidecar();
  if (dataDir) await rm(dataDir, { recursive: true, force: true });
  dataDir = null;
}

async function ejecutarHarness() {
  let codigoSalida = 1;
  try {
    comprobarPrecondiciones();
    dataDir = await mkdtemp(join(tmpdir(), "nyanko-reader-rss-"));
    const biblioteca = await prepararBibliotecaTemporal(dataDir);
    arrancarSidecar(dataDir);
    const puerto = await esperarSidecar(dataDir);
    sembrarEntradaLocalParaElShell(dataDir);
    await registrarBiblioteca(puerto, biblioteca, dataDir);
    registrarIpc(dataDir);
    ventana = await abrirAplicacion();
    await abrirPrimerCapitulo();
    const { rssFinalMB, picoRssMB } = await recorrerCapitulo();
    const fallo = picoRssMB > TECHO_RSS_MB;
    console.log(
      `RSS renderer: ${rssFinalMB.toFixed(2)} MB `
      + `(pico ${picoRssMB.toFixed(2)} MB; techo ${TECHO_RSS_MB} MB) -> ${fallo ? "FALLO" : "OK"}`,
    );
    codigoSalida = fallo ? 1 : 0;
  } catch (error) {
    const detalle = salidaSidecar.trim();
    console.error(
      `FALLO reader RSS: ${error instanceof Error ? error.message : String(error)}`
      + (detalle ? `\nUltima salida del sidecar:\n${detalle}` : ""),
    );
  } finally {
    try {
      await limpiar();
    } catch (error) {
      codigoSalida = 1;
      console.error(`FALLO reader RSS: no se pudo limpiar el entorno temporal: ${error.message}`);
    }
    app.exit(codigoSalida);
  }
}

app.whenReady().then(ejecutarHarness).catch(async (error) => {
  console.error(`FALLO reader RSS: Electron no entro en ready: ${error.message}`);
  try {
    await limpiar();
  } catch (errorLimpieza) {
    console.error(`FALLO reader RSS: no se pudo limpiar el entorno temporal: ${errorLimpieza.message}`);
  } finally {
    app.exit(1);
  }
});
