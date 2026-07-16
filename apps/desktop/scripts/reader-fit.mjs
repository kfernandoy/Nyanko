#!/usr/bin/env node

// Gate de layout del reader: mide con getBoundingClientRect() que cada ajuste
// (ancho/alto/original) encaja la pagina donde debe, en LTR, RTL y doble pagina.
//
// Existe porque el hallazgo #3 del UAT de la 03 (fit-height cortaba la pagina) NO se
// podia decidir leyendo el CSS: la cadena de alturas dependia de si `.reader-paged`
// (grid + place-items:center) hacia definida la altura de su fila, y las dos lecturas
// eran defendibles sobre el papel. Solo la medicion decidio. Este harness es esa
// medicion, congelada: si alguien reintroduce un eslabon de altura indefinida,
// `height:100%` y `max-height:100%` de la img degradan a auto/none, la img se pinta a
// su altura natural y esta comprobacion sale en rojo.

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

const TOTAL_PAGINAS = 4;
const ANCHO_PAGINA = 2000;
const ALTO_PAGINA = 3000;
const TIMEOUT_SIDECAR_MS = 30_000;
const TIMEOUT_RENDERER_MS = 60_000;
// Redondeos subpixel del layout: 1px de margen es holgado para un rect y estrecho
// frente al fallo que vigila (una pagina de 3000px dentro de un stage de ~686px).
const TOLERANCIA_PX = 1;

// Sin este listener vacio, cerrar la ultima ventana termina la app CON CODIGO 0 y ese
// quit(0) gana la carrera contra app.exit(codigoSalida) de limpiar(). El harness de
// RD-09 ya mordio ese falso verde: imprimia FALLO y devolvia 0.
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
  const cache = join(tmpdir(), "nyanko-reader-fit-2000x3000-v1");
  const capitulo = join(directorio, "biblioteca", "Serie", "Cap 1");
  await mkdir(cache, { recursive: true });
  await mkdir(capitulo, { recursive: true });

  for (let indice = 1; indice <= TOTAL_PAGINAS; indice += 1) {
    const nombre = nombrePagina(indice);
    const cacheada = join(cache, nombre);
    if (!(await existeConContenido(cacheada))) {
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
  const base = new DatabaseSync(join(directorio, "nyanko.sqlite3"));
  try {
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

// React ignora un `select.value = x` a secas: su value tracker cree que nada cambio y
// se come el evento. Hay que escribir por el setter nativo del prototipo para que el
// tracker se entere y el onChange del componente llegue a correr.
const CAMBIAR_SELECT = `(selector, valor) => {
  const select = [...document.querySelectorAll('.reader-controls select')]
    .find((candidato) => [...candidato.options].some((opcion) => opcion.value === selector));
  if (!select) throw new Error('no hay ningun select con la opcion ' + selector);
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  setter.call(select, valor);
  select.dispatchEvent(new Event('change', { bubbles: true }));
}`;

async function ponerAjuste(ajuste) {
  await ejecutarEnRenderer(`(${CAMBIAR_SELECT})('original', ${JSON.stringify(ajuste)}); true`);
  await esperarCondicion(
    `Boolean(document.querySelector('.reader-pages.reader-fit-${ajuste}'))`,
    `el ajuste ${ajuste} no se aplico`,
  );
}

async function ponerModo(modo) {
  await ejecutarEnRenderer(`(${CAMBIAR_SELECT})('vertical', ${JSON.stringify(modo)}); true`);
  await esperarCondicion(
    `Boolean(document.querySelector('.reader-pages.reader-direction-${modo}'))`,
    `el modo ${modo} no se aplico`,
  );
}

async function ponerDoblePagina(activada) {
  await ejecutarEnRenderer(`(() => {
    const caja = document.querySelector('.reader-check input[type=checkbox]');
    if (!caja) throw new Error('no hay checkbox de doble pagina');
    if (caja.checked !== ${activada}) caja.click();
  })(); true`);
  await esperarCondicion(
    `document.querySelectorAll('.reader-page--visible').length === ${activada ? 2 : 1}`,
    `la doble pagina no quedo ${activada ? "activada" : "desactivada"}`,
  );
}

// Dos rAF encadenados: el primero cede hasta el frame en el que React ya pinto, el
// segundo garantiza que el layout de ese frame esta resuelto antes de medir.
const MEDIR = `new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => {
  const rect = (elemento) => {
    if (!elemento) return null;
    const caja = elemento.getBoundingClientRect();
    return { w: Number(caja.width.toFixed(2)), h: Number(caja.height.toFixed(2)) };
  };
  const imagenes = [...document.querySelectorAll('.reader-page--visible img')];
  resolve({
    titlebar: Boolean(document.querySelector('.titlebar')),
    reader: rect(document.querySelector('.reader')),
    stage: rect(document.querySelector('.reader-stage')),
    pages: rect(document.querySelector('.reader-pages')),
    slots: [...document.querySelectorAll('.reader-page--visible')].map(rect),
    imgs: imagenes.map((imagen) => ({
      ...rect(imagen),
      nw: imagen.naturalWidth,
      nh: imagen.naturalHeight,
      completa: imagen.complete,
    })),
  });
})))`;

async function medir() {
  const medicion = await ejecutarEnRenderer(MEDIR);
  if (!medicion.stage || !medicion.pages) throw new Error("no se encontro el stage o el contenedor de paginas");
  if (medicion.imgs.length === 0) throw new Error("no hay ninguna imagen visible que medir");
  for (const imagen of medicion.imgs) {
    if (!imagen.completa || imagen.nw !== ANCHO_PAGINA || imagen.nh !== ALTO_PAGINA) {
      throw new Error(`una pagina no cargo a ${ANCHO_PAGINA}x${ALTO_PAGINA} (${imagen.nw}x${imagen.nh})`);
    }
  }
  return medicion;
}

function describir(medicion) {
  const imagenes = medicion.imgs.map((imagen) => `${imagen.w}x${imagen.h}`).join(" + ");
  return `stage ${medicion.stage.w}x${medicion.stage.h} | pages ${medicion.pages.w}x${medicion.pages.h} `
    + `| slots ${medicion.slots.map((slot) => `${slot.w}x${slot.h}`).join(" + ")} | img ${imagenes}`;
}

const igual = (a, b) => Math.abs(a - b) <= TOLERANCIA_PX;

// Cada caso devuelve la lista de motivos por los que falla. Vacia = OK.
function comprobar(ajuste, medicion) {
  const motivos = [];
  const { stage, pages, slots, imgs } = medicion;

  // LA INVARIANTE DE LA CAUSA RAIZ, y vale para los tres ajustes: la cadena de alturas
  // del stage hasta el hueco de pagina tiene que ser DEFINIDA. En cuanto un eslabon se
  // vuelve indefinido, `height:100%` deja de resolver, el contenedor crece hasta el alto
  // natural de la pagina y los porcentajes de la img degradan. Se comprueba aqui, y no
  // solo mirando la img, porque este es el eslabon que se rompio y el que mide el fallo
  // sin depender de que ajuste este puesto.
  if (!igual(pages.w, stage.w) || !igual(pages.h, stage.h)) {
    motivos.push(
      `.reader-pages mide ${pages.w}x${pages.h} y deberia calcar el stage (${stage.w}x${stage.h}): `
      + "su height/width:100% no resuelve, la cadena tiene un eslabon indefinido",
    );
  }
  for (const [indice, hueco] of slots.entries()) {
    if (!igual(hueco.h, stage.h)) {
      motivos.push(`el hueco de pagina ${indice + 1} mide ${hueco.h}px de alto y el stage ${stage.h}px: su height:100% no resuelve`);
    }
  }

  for (const [indice, imagen] of imgs.entries()) {
    const hueco = slots[indice];
    if (ajuste === "original") {
      // «Original» es 1:1 por definicion: DEBE desbordar un stage mas pequeno que la
      // pagina. Se mide para tener el contraste, no para exigirle que quepa.
      if (!igual(imagen.w, ANCHO_PAGINA) || !igual(imagen.h, ALTO_PAGINA)) {
        motivos.push(`original deberia pintar a tamano natural ${ANCHO_PAGINA}x${ALTO_PAGINA}, pinta ${imagen.w}x${imagen.h}`);
      }
    } else if (ajuste === "width") {
      // «Ancho» ajusta al ANCHO: llena su hueco y el alto sale por aspecto, aunque eso
      // desborde el stage. Exigirle que quepa entera seria pedirle que se comporte como
      // «alto» — y ahi es donde `max-height:100%` lo apaisaria a ~457px.
      if (!igual(imagen.w, hueco.w)) {
        motivos.push(`el ajuste ancho deberia llenar los ${hueco.w}px de su hueco, usa ${imagen.w}px`);
      }
    } else {
      // «Alto» ajusta al ALTO y ademas debe verse ENTERA: usa toda la altura del stage y
      // no rebasa su hueco a lo ancho. Es el hallazgo #3, literal.
      if (!igual(imagen.h, stage.h)) {
        motivos.push(`el ajuste alto deberia usar los ${stage.h}px del stage, usa ${imagen.h}px`);
      }
      if (imagen.w > hueco.w + TOLERANCIA_PX) {
        motivos.push(`la img mide ${imagen.w}px de ancho y su hueco ${hueco.w}px: la pagina sale recortada`);
      }
    }
  }

  return motivos;
}

async function medirCaso(nombre, ajuste) {
  const medicion = await medir();
  const motivos = comprobar(ajuste, medicion);
  console.log(`${motivos.length === 0 ? "OK  " : "FALLO"} ${nombre.padEnd(28)} ${describir(medicion)}`);
  for (const motivo of motivos) console.log(`      -> ${motivo}`);
  return motivos.length === 0;
}

async function recorrerAjustes() {
  const ajustes = ["width", "height", "original"];
  let todoOk = true;

  for (const modo of ["ltr", "rtl"]) {
    await ponerModo(modo);
    await ponerDoblePagina(false);
    for (const ajuste of ajustes) {
      await ponerAjuste(ajuste);
      todoOk = await medirCaso(`${modo} / ajuste ${ajuste}`, ajuste) && todoOk;
    }
  }

  // Doble pagina solo en LTR: comparte la misma cadena de alturas que RTL (lo unico
  // que cambia es flex-direction), asi que repetirla en RTL no mide nada nuevo.
  await ponerModo("ltr");
  await ponerDoblePagina(true);
  for (const ajuste of ajustes) {
    await ponerAjuste(ajuste);
    todoOk = await medirCaso(`ltr doble / ajuste ${ajuste}`, ajuste) && todoOk;
  }

  return todoOk;
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
    dataDir = await mkdtemp(join(tmpdir(), "nyanko-reader-fit-"));
    const biblioteca = await prepararBibliotecaTemporal(dataDir);
    arrancarSidecar(dataDir);
    const puerto = await esperarSidecar(dataDir);
    sembrarEntradaLocalParaElShell(dataDir);
    await registrarBiblioteca(puerto, biblioteca, dataDir);
    registrarIpc(dataDir);
    ventana = await abrirAplicacion();
    await abrirPrimerCapitulo();
    const todoOk = await recorrerAjustes();
    console.log(todoOk ? "\nAjustes del reader: OK" : "\nAjustes del reader: FALLO");
    codigoSalida = todoOk ? 0 : 1;
  } catch (error) {
    const detalle = salidaSidecar.trim();
    console.error(
      `FALLO reader fit: ${error instanceof Error ? error.message : String(error)}`
      + (detalle ? `\nUltima salida del sidecar:\n${detalle}` : ""),
    );
  } finally {
    try {
      await limpiar();
    } catch (error) {
      codigoSalida = 1;
      console.error(`FALLO reader fit: no se pudo limpiar el entorno temporal: ${error.message}`);
    }
    app.exit(codigoSalida);
  }
}

app.whenReady().then(ejecutarHarness).catch(async (error) => {
  console.error(`FALLO reader fit: Electron no entro en ready: ${error.message}`);
  try {
    await limpiar();
  } catch (errorLimpieza) {
    console.error(`FALLO reader fit: no se pudo limpiar el entorno temporal: ${errorLimpieza.message}`);
  } finally {
    app.exit(1);
  }
});
