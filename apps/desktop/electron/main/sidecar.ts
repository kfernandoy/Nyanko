import { spawn, execFile, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

// NATIVE-02: ciclo de vida del sidecar Python (nyanko-api.exe) en prod.
// Mismo split que compat-paths.ts: helpers PUROS (Electron-free) como exports
// nombrados para que sidecar.test.ts los ejerza bajo Node plano, y wrappers
// finos con spawn/taskkill/net (no testeados) aparte.

// ── Helpers puros (self-checkables) ──

// Mirror de instance.py read_port_file: int(text.strip()), null si NaN/vacío.
// Number() rechaza floats y basura ("87.5"→null, "nope"→null) igual que int().
export function parsePortFile(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isInteger(n) ? n : null;
}

// D-10: dev = !app.isPackaged. Booleano puro para que el self-check lo maneje
// sin Electron. En dev el spawn se omite (backend a mano) — decisión en index.ts.
export function isDevMode(isPackaged: boolean): boolean {
  return !isPackaged;
}

// D-03: endpoint de readiness. Host fijo 127.0.0.1 (T-02-HOST: sin egress remoto,
// solo el puerto es variable).
export function healthUrl(port: number): string {
  return `http://127.0.0.1:${port}/api/health`;
}

// T-02-INJ: ruta ABSOLUTA del exe. Override explícito (NYANKO_SIDECAR_EXE) o el
// layout extraResources de Phase 5. Nunca un nombre PATH-resuelto.
export function resolveSidecarExe(): string {
  const override = process.env.NYANKO_SIDECAR_EXE;
  if (override) return override;
  return join(process.resourcesPath, "nyanko-api", "nyanko-api.exe");
}

// ── Wrappers finos (spawn / net / taskkill — NO unit-tested) ──

const PORT_FILE_WAIT_MS = 30_000; // ventana total: port file + readiness
const POLL_MS = 200;
const KILL_GRACEFUL_MS = 4_000;
const RESPAWN_DELAY_MS = 800;

export interface StartSidecarOptions {
  dataDir: string; // ABSOLUTO — el mismo userData que index.ts lockea (anti 6-DBs)
}

let child: ChildProcess | null = null;

// D-01/D-04/D-05/D-06: borra el port viejo, spawnea, espera port file + health
// 200; fail-fast si el .exe sale pronto; UN re-spawn automático antes de rechazar.
export async function startSidecar(opts: StartSidecarOptions): Promise<number> {
  try {
    return await spawnAndWait(opts.dataDir);
  } catch (firstErr) {
    // D-05: cleanup (matar el child propio + borrar port), esperar, y
    // D-06: EXACTAMENTE un re-spawn. El segundo fallo propaga → splash error (Plan 02).
    await killSidecar();
    rmPortFile(opts.dataDir);
    await delay(RESPAWN_DELAY_MS);
    return await spawnAndWait(opts.dataDir);
  }
}

async function spawnAndWait(dataDir: string): Promise<number> {
  const portFile = join(dataDir, "port");
  // D-01 step 2: borrar el port viejo ANTES del spawn — el wait solo acepta un
  // port file escrito tras este spawn (evita leer un puerto obsoleto).
  rmPortFile(dataDir);

  const exe = resolveSidecarExe();
  child = spawn(exe, [], {
    // T-02-INJ: shell:false + ruta absoluta; NYANKO_DATA_DIR absoluto = el mismo
    // userData que main lockea (config.py ancla un data_dir relativo a apps/backend).
    shell: false,
    windowsHide: true,
    env: { ...process.env, NYANKO_DATA_DIR: dataDir },
  });
  // Import diferido: logging.ts carga electron/electron-log, que no existen bajo
  // Node plano. Diferirlo mantiene los helpers puros importables por el self-check
  // (sidecar.test.ts) sin bootear Electron; solo el spawn real (prod) lo necesita.
  const { pipeSidecarOutput } = await import("./logging");
  pipeSidecarOutput(child); // OBS-01: sidecar.log

  // D-04 fail-fast: capturar exit temprano en vez de esperar los 30s.
  let earlyExit: number | null | undefined;
  child.once("exit", (code) => {
    earlyExit = code;
  });

  const deadline = Date.now() + PORT_FILE_WAIT_MS;

  // Paso 4: esperar el port file (≤30s).
  let port: number | null = null;
  while (Date.now() < deadline) {
    if (earlyExit !== undefined) {
      throw new Error(`sidecar salió pronto (code=${earlyExit}) antes del port file`);
    }
    if (existsSync(portFile)) {
      port = parsePortFile(readFileSync(portFile, "utf-8"));
      if (port !== null) break;
    }
    await delay(POLL_MS);
  }
  if (port === null) throw new Error("timeout esperando el port file del sidecar");

  // Paso 5: readiness real GET /api/health → 200 en la ventana restante (D-03).
  const url = healthUrl(port);
  while (Date.now() < deadline) {
    if (earlyExit !== undefined) {
      throw new Error(`sidecar salió pronto (code=${earlyExit}) durante readiness`);
    }
    try {
      const res = await fetch(url);
      if (res.status === 200) return port;
    } catch {
      // aún no escucha — reintentar
    }
    await delay(POLL_MS);
  }
  throw new Error("timeout esperando GET /api/health 200");
}

// D-07/D-08: kill único reusable (before-quit del Plan 02 y quitAndInstall del
// updater en Phase 5 llaman esta MISMA ruta). Graceful a nivel SO (backend
// congelado, sin /api/shutdown D-09) → taskkill /T /F del árbol PyInstaller.
// No-op si no hay child corriendo.
export async function killSidecar(): Promise<void> {
  const proc = child;
  if (!proc || proc.pid === undefined || proc.exitCode !== null) {
    child = null;
    return;
  }
  const pid = proc.pid;
  proc.kill(); // intento ordenado
  const gone = await waitExit(proc, KILL_GRACEFUL_MS);
  if (!gone) {
    // /T mata el árbol: PyInstaller onedir lanza un proceso hijo en Windows.
    await new Promise<void>((resolve) => {
      execFile("taskkill", ["/PID", String(pid), "/T", "/F"], () => resolve());
    });
  }
  child = null;
}

function waitExit(proc: ChildProcess, ms: number): Promise<boolean> {
  if (proc.exitCode !== null) return Promise.resolve(true);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), ms);
    proc.once("exit", () => {
      clearTimeout(timer);
      resolve(true);
    });
  });
}

function rmPortFile(dataDir: string): void {
  rmSync(join(dataDir, "port"), { force: true });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
