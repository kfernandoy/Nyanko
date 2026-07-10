import { app, shell } from "electron";
import log from "electron-log/main";
import { createWriteStream } from "node:fs";
import { join } from "node:path";
import type { ChildProcess } from "node:child_process";

// OBS-01: rastro diagnóstico desde la primera versión Electron. main.log (este
// proceso via electron-log) y sidecar.log (stdout/stderr del .exe) son ficheros
// DISTINTOS bajo app.getPath('logs'). Módulo Electron-thin: no hay lógica pura
// que testear (todo es I/O de Electron), así que no lleva self-check propio.

// Inicializa electron-log fijando main.log bajo app.getPath('logs'). Rotación,
// nivel y formato quedan en los defaults de electron-log (Claude's Discretion,
// CONTEXT) — no se hand-rollea config sin necesidad.
export function setupLogging(): void {
  log.transports.file.resolvePathFn = () => join(app.getPath("logs"), "main.log");
  // Una línea de arranque garantiza que main.log exista tras setupLogging().
  log.info("Nyanko main iniciado");
}

// D-11 / T-02-IPC: SIN argumento a propósito. El destino es SIEMPRE
// app.getPath('logs'); nunca una ruta que venga del renderer. Un path
// atacante-controlado abriría cualquier carpeta del sistema, así que esta es la
// única función que abre logs y no acepta parámetros (la reusan el handler IPC
// del Plan 02 y el item de menú nativo opcional, D-12).
export function openLogsFolder(): Promise<string> {
  return shell.openPath(app.getPath("logs"));
}

// Pipea stdout+stderr del sidecar a sidecar.log (fichero aparte de main.log).
// Write stream plano en modo append — lo más simple que mantiene los dos logs
// separados (Claude's Discretion: stream vs transport de electron-log).
export function pipeSidecarOutput(child: ChildProcess): void {
  const sink = createWriteStream(join(app.getPath("logs"), "sidecar.log"), { flags: "a" });
  child.stdout?.pipe(sink);
  child.stderr?.pipe(sink);
}
