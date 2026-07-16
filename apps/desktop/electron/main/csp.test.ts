import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const mainDir = dirname(fileURLToPath(import.meta.url));
const escritorioDir = resolve(mainDir, "../..");
const indexHtml = readFileSync(resolve(escritorioDir, "index.html"), "utf8");
const config = readFileSync(resolve(escritorioDir, "electron.vite.config.ts"), "utf8");
const splash = readFileSync(resolve(mainDir, "splash.ts"), "utf8");
const principal = readFileSync(resolve(mainDir, "index.ts"), "utf8");

function directivasDe(nombre: string, siguiente: string): string {
  const inicio = config.indexOf(`const ${nombre} = [`);
  const fin = config.indexOf(siguiente, inicio);
  assert.ok(inicio >= 0 && fin > inicio, `no se encontro el bloque ${nombre}`);
  return [...config.slice(inicio, fin).matchAll(/^\s*"([^"]+)"[,]?$/gm)]
    .map((coincidencia) => coincidencia[1])
    .join("; ");
}

const produccion = directivasDe("CSP_PRODUCCION", "const CSP_DESARROLLO");
const desarrollo = directivasDe("CSP_DESARROLLO", "function cspPlugin");

test("index.html lleva la CSP como meta y el config sustituye su marcador", () => {
  assert.match(indexHtml, /<meta\s+http-equiv="Content-Security-Policy"\s+content="%CSP%"\s*\/>/);
  assert.match(config, /replaceAll\("%CSP%"/);
});

test("la CSP de produccion conserva reader, portadas y playbackSocket", () => {
  assert.match(produccion, /img-src 'self' http:\/\/127\.0\.0\.1:\* https: blob: data:/);
  assert.match(produccion, /connect-src 'self' http:\/\/127\.0\.0\.1:\* ws:\/\/127\.0\.0\.1:\*/);
  assert.match(produccion, /style-src 'self' 'unsafe-inline'/);
});

test("la concesion de scripts inline queda solo en desarrollo", () => {
  assert.match(produccion, /script-src 'self'(?:;|$)/);
  assert.doesNotMatch(produccion, /script-src[^;]*'unsafe-inline'/);
  assert.match(desarrollo, /script-src 'self' 'unsafe-inline'/);
  assert.match(desarrollo, /http:\/\/localhost:1420/);
  assert.match(desarrollo, /ws:\/\/localhost:1420/);
  const evaluacionInsegura = "'unsafe-" + "eval'";
  assert.equal(`${produccion}\n${desarrollo}\n${splash}`.includes(evaluacionInsegura), false);
});

test("el splash no tiene red y conserva sus tres botones inline", () => {
  assert.match(
    splash,
    /<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"/,
  );
  assert.equal((splash.match(/onclick=/g) ?? []).length, 3);
});

test("las dos ventanas mantienen las preferencias seguras", () => {
  for (const [nombre, fuente] of [["principal", principal], ["splash", splash]] as const) {
    assert.match(fuente, /contextIsolation:\s*true/, `${nombre}: contextIsolation debe seguir activo`);
    assert.match(fuente, /nodeIntegration:\s*false/, `${nombre}: nodeIntegration debe seguir desactivado`);
    assert.match(fuente, /sandbox:\s*true/, `${nombre}: sandbox debe seguir activo`);
    assert.match(fuente, /webSecurity:\s*true/, `${nombre}: webSecurity debe seguir activo`);
  }
});

test("la CSP no se inyecta mediante cabeceras de sesion", () => {
  const fuente = `${principal}\n${splash}\n${config}`;
  const hookCabeceras = ["onHeaders", "Received"].join("");
  const apiSesion = ["web", "Request"].join("");
  assert.equal(fuente.includes(hookCabeceras), false);
  assert.equal(fuente.includes(apiSesion), false);
});
